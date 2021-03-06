import ROOT
from ROOT import TFile, TTree, TChain, gPad, gDirectory
from multiprocessing import Process
from optparse import OptionParser
from operator import add
import math
import array
import scipy
import pdb
import sys
import time
import warnings

PTCUT = 450.
PTCUTMUCR = 400.
DBTAGCUT = 0.9
T21DDTCUT = 0.55
MUONPTCUT = 55
METCUT = 140
MASSCUT = 40
NJETCUT = 100

def delta_phi(phi1, phi2):
  PI = 3.14159265359
  x = phi1 - phi2
  while x >=  PI:
      x -= ( 2*PI )
  while x <  -PI:
      x += ( 2*PI )
  return x

def delta_phi_david(phi1, phi2):
    return math.acos(math.cos(phi1 - phi2))

#########################################################################################################
class sampleContainerPhibb:
    def __init__(self, name, fn, sf=1, DBTAGCUTMIN=-99., lumi=1, isData=False, fillCA15=False, cutFormula='1', minBranches=False):
        self._name = name
        self.DBTAGCUTMIN = DBTAGCUTMIN
        self._fn = fn
        if len(fn) > 0:
            self._tf = ROOT.TFile.Open(self._fn[0])
        self._tt = ROOT.TChain('otree')
        for fn in self._fn: self._tt.Add(fn)
        self._sf = sf
        self._lumi = lumi
        self._fillCA15 = fillCA15
        warnings.filterwarnings(action='ignore', category=RuntimeWarning, message='creating converter.*')
        if not self._fillCA15 : 
            self._cutFormula = ROOT.TTreeFormula("cutFormula", "(" + cutFormula + ")&&(AK8Puppijet0_pt>%f||AK8Puppijet0_pt_JESDown>%f||AK8Puppijet0_pt_JESUp>%f||AK8Puppijet0_pt_JERUp>%f||AK8Puppijet0_pt_JERDown>%f)" % (PTCUTMUCR, PTCUTMUCR, PTCUTMUCR, PTCUTMUCR, PTCUTMUCR), self._tt)
        else: 
            self._cutFormula = ROOT.TTreeFormula("cutFormula", "(" + cutFormula + ")&&(CA15Puppijet0_pt>%f||CA15Puppijet0_pt_JESDown>%f||CA15Puppijet0_pt_JESUp>%f||CA15Puppijet0_pt_JERUp>%f||CA15Puppijet0_pt_JERDown>%f)" % (PTCUTMUCR, PTCUTMUCR, PTCUTMUCR, PTCUTMUCR, PTCUTMUCR), self._tt)

        self._isData = isData
        # print lumi
        # print self._NEv.GetBinContent(1)
        if isData:
            self._lumi = 1
        # based on https://github.com/thaarres/PuppiSoftdropMassCorr Summer16
        self.corrGEN = ROOT.TF1("corrGEN", "[0]+[1]*pow(x*[2],-[3])", 200, 3500)
        self.corrGEN.SetParameter(0, 1.00626)
        self.corrGEN.SetParameter(1, -1.06161)
        self.corrGEN.SetParameter(2, 0.0799900)
        self.corrGEN.SetParameter(3, 1.20454)

        self.corrRECO_cen = ROOT.TF1("corrRECO_cen", "[0]+[1]*x+[2]*pow(x,2)+[3]*pow(x,3)+[4]*pow(x,4)+[5]*pow(x,5)",
                                     200, 3500)
        self.corrRECO_cen.SetParameter(0, 1.09302)
        self.corrRECO_cen.SetParameter(1, -0.000150068)
        self.corrRECO_cen.SetParameter(2, 3.44866e-07)
        self.corrRECO_cen.SetParameter(3, -2.68100e-10)
        self.corrRECO_cen.SetParameter(4, 8.67440e-14)
        self.corrRECO_cen.SetParameter(5, -1.00114e-17)

        self.corrRECO_for = ROOT.TF1("corrRECO_for", "[0]+[1]*x+[2]*pow(x,2)+[3]*pow(x,3)+[4]*pow(x,4)+[5]*pow(x,5)",
                                     200, 3500)
        self.corrRECO_for.SetParameter(0, 1.27212)
        self.corrRECO_for.SetParameter(1, -0.000571640)
        self.corrRECO_for.SetParameter(2, 8.37289e-07)
        self.corrRECO_for.SetParameter(3, -5.20433e-10)
        self.corrRECO_for.SetParameter(4, 1.45375e-13)
        self.corrRECO_for.SetParameter(5, -1.50389e-17)

        # f_puppi= ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ZqqJet/puppiCorr.root","read")
        # self._puppisd_corrGEN      = f_puppi.Get("puppiJECcorr_gen")
        # self._puppisd_corrRECO_cen = f_puppi.Get("puppiJECcorr_reco_0eta1v3")
        # self._puppisd_corrRECO_for = f_puppi.Get("puppiJECcorr_reco_1v3eta2v5")

        f_pu = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/puWeights_All.root", "read")
        self._puw = f_pu.Get("puw")
        self._puw_up = f_pu.Get("puw_p")
        self._puw_down = f_pu.Get("puw_m")

        # get histogram for transform
        if not self._fillCA15: f_h2ddt = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ZqqJet/h3_n2ddt_26eff_36binrho11pt_Spring16.root", "read")  # GridOutput_v13_WP026.root # smooth version of the ddt ; exp is 4.45 vs 4.32 (3% worse)          AK8
        else: f_h2ddt = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/PbbJet/h3_n2ddt_CA15.root", "read")  # GridOutput_v13_WP026.root # smooth version of the ddt ; exp is 4.45 vs 4.32 (3% worse)    CA15
        self._trans_h2ddt = f_h2ddt.Get("h2ddt")
        self._trans_h2ddt.SetDirectory(0)
        f_h2ddt.Close()

        # get trigger efficiency object

        if not self._fillCA15: 
            f_trig = ROOT.TFile.Open( "$ZPRIMEPLUSJET_BASE/analysis/ggH/RUNTriggerEfficiencies_SingleMuon_Run2016_V2p1_v03.root", "read")   #AK8
            self._trig_denom = f_trig.Get("DijetTriggerEfficiencySeveralTriggers/jet1SoftDropMassjet1PtDenom_cutJet")
            self._trig_numer = f_trig.Get("DijetTriggerEfficiencySeveralTriggers/jet1SoftDropMassjet1PtPassing_cutJet")
        else:
            f_trig = ROOT.TFile.Open( "$ZPRIMEPLUSJET_BASE/analysis/ggH/RUNTriggerEfficiencies_SingleMuon_Run2016_V2p4_v08.root", "read")   #CA15
            self._trig_denom = f_trig.Get("DijetCA15TriggerEfficiencySeveralTriggers/jet1SoftDropMassjet1PtDenom_cutJet")
            self._trig_numer = f_trig.Get("DijetCA15TriggerEfficiencySeveralTriggers/jet1SoftDropMassjet1PtPassing_cutJet")
        self._trig_denom.SetDirectory(0)
        self._trig_numer.SetDirectory(0)
        self._trig_denom.RebinX(2)
        self._trig_numer.RebinX(2)
        self._trig_denom.RebinY(5)
        self._trig_numer.RebinY(5)
        self._trig_eff = ROOT.TEfficiency()
        if (ROOT.TEfficiency.CheckConsistency(self._trig_numer, self._trig_denom)):
            self._trig_eff = ROOT.TEfficiency(self._trig_numer, self._trig_denom)
            self._trig_eff.SetDirectory(0)
        f_trig.Close()

        # get muon trigger efficiency object

        lumi_GH = 16.146
        lumi_BCDEF = 19.721
        lumi_total = lumi_GH + lumi_BCDEF

        f_mutrig_GH = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_Period4.root", "read")
        self._mutrig_eff_GH = f_mutrig_GH.Get("Mu50_OR_TkMu50_PtEtaBins/efficienciesDATA/pt_abseta_DATA")
        self._mutrig_eff_GH.Sumw2()
        self._mutrig_eff_GH.SetDirectory(0)
        f_mutrig_GH.Close()

        f_mutrig_BCDEF = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_RunBtoF.root", "read")
        self._mutrig_eff_BCDEF = f_mutrig_BCDEF.Get("Mu50_OR_TkMu50_PtEtaBins/efficienciesDATA/pt_abseta_DATA")
        self._mutrig_eff_BCDEF.Sumw2()
        self._mutrig_eff_BCDEF.SetDirectory(0)
        f_mutrig_BCDEF.Close()

        self._mutrig_eff = self._mutrig_eff_GH.Clone('pt_abseta_DATA_mutrig_ave')
        self._mutrig_eff.Scale(lumi_GH / lumi_total)
        self._mutrig_eff.Add(self._mutrig_eff_BCDEF, lumi_BCDEF / lumi_total)

        # get muon ID efficiency object

        f_muid_GH = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_GH.root", "read")
        self._muid_eff_GH = f_muid_GH.Get("MC_NUM_LooseID_DEN_genTracks_PAR_pt_eta/efficienciesDATA/pt_abseta_DATA")
        self._muid_eff_GH.Sumw2()
        self._muid_eff_GH.SetDirectory(0)
        f_muid_GH.Close()

        f_muid_BCDEF = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_BCDEF.root", "read")
        self._muid_eff_BCDEF = f_muid_BCDEF.Get(
            "MC_NUM_LooseID_DEN_genTracks_PAR_pt_eta/efficienciesDATA/pt_abseta_DATA")
        self._muid_eff_BCDEF.Sumw2()
        self._muid_eff_BCDEF.SetDirectory(0)
        f_muid_BCDEF.Close()

        self._muid_eff = self._muid_eff_GH.Clone('pt_abseta_DATA_muid_ave')
        self._muid_eff.Scale(lumi_GH / lumi_total)
        self._muid_eff.Add(self._muid_eff_BCDEF, lumi_BCDEF / lumi_total)

        # get muon ISO efficiency object

        f_muiso_GH = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_ISO_GH.root", "read")
        self._muiso_eff_GH = f_muiso_GH.Get("LooseISO_LooseID_pt_eta/efficienciesDATA/pt_abseta_DATA")
        self._muiso_eff_GH.Sumw2()
        self._muiso_eff_GH.SetDirectory(0)
        f_muiso_GH.Close()

        f_muiso_BCDEF = ROOT.TFile.Open("$ZPRIMEPLUSJET_BASE/analysis/ggH/EfficienciesAndSF_ISO_BCDEF.root", "read")
        self._muiso_eff_BCDEF = f_muiso_BCDEF.Get("LooseISO_LooseID_pt_eta/efficienciesDATA/pt_abseta_DATA")
        self._muiso_eff_BCDEF.Sumw2()
        self._muiso_eff_BCDEF.SetDirectory(0)
        f_muiso_BCDEF.Close()

        self._muiso_eff = self._muiso_eff_GH.Clone('pt_abseta_DATA_muiso_ave')
        self._muiso_eff.Scale(lumi_GH / lumi_total)
        self._muiso_eff.Add(self._muiso_eff_BCDEF, lumi_BCDEF / lumi_total)

        self._minBranches = minBranches
        # set branch statuses and addresses
        #Common
        self._branches = [('puWeight', 'f', 0), ('scale1fb', 'f', 0),
                          ('kfactor', 'f', 0), ('kfactorNLO', 'f', 0), ('nAK4PuppijetsPt30', 'i', -999),
                          ('nAK4PuppijetsPt30dR08_0', 'i', -999),
                          ('nAK4PuppijetsPt30dR08jesUp_0', 'i', -999), ('nAK4PuppijetsPt30dR08jesDown_0', 'i', -999),
                          ('nAK4PuppijetsPt30dR08jerUp_0', 'i', -999), ('nAK4PuppijetsPt30dR08jerDown_0', 'i', -999),
                          ('nAK4PuppijetsMPt50dR08_0', 'i', -999),
                          ('AK8Puppijet0_ratioCA15_04', 'd', -999),
                          ('pfmet', 'f', -999), ('pfmetphi', 'f', -999), ('puppet', 'f', -999),
                          ('puppetphi', 'f', -999),
                          ('MetXCorrjesUp', 'd', -999), ('MetXCorrjesDown', 'd', -999), ('MetYCorrjesUp', 'd', -999),
                          ('MetYCorrjesDown', 'd', -999),
                          ('MetXCorrjerUp', 'd', -999), ('MetXCorrjerDown', 'd', -999), ('MetYCorrjerUp', 'd', -999),
                          ('MetYCorrjerDown', 'd', -999),
                          ('neleLoose', 'i', -999), ('nmuLoose', 'i', -999), ('ntau', 'i', -999),
                          ('nphoLoose', 'i', -999),
                          ('triggerBits', 'i', 1), ('passJson', 'i', 1), ('vmuoLoose0_pt', 'd', -999),
                          ('vmuoLoose0_eta', 'd', -999), ('vmuoLoose0_phi', 'd', -999),
                          ('npv', 'i', 1), ('npu', 'i', 1)
                          ]
        
        if not self._minBranches:
            self._branches.extend([('nAK4PuppijetsfwdPt30', 'i', -999), ('nAK4PuppijetsLPt50dR08_0', 'i', -999),
                                   ('nAK4PuppijetsTPt50dR08_0', 'i', -999),
                                   ('nAK4PuppijetsLPt100dR08_0', 'i', -999), ('nAK4PuppijetsMPt100dR08_0', 'i', -999),
                                   ('nAK4PuppijetsTPt100dR08_ 0', 'i', -999),
                                   ('nAK4PuppijetsLPt150dR08_0', 'i', -999), ('nAK4PuppijetsMPt150dR08_0', 'i', -999),
                                   ('nAK4PuppijetsTPt150dR08_0', 'i', -999),
                                   ('nAK4PuppijetsLPt50dR08_1', 'i', -999), ('nAK4PuppijetsMPt50dR08_1', 'i', -999),
                                   ('nAK4PuppijetsTPt50dR08_1', 'i', -999),
                                   ('nAK4PuppijetsLPt100dR08_1', 'i', -999), ('nAK4PuppijetsMPt100dR08_1', 'i', -999),
                                   ('nAK4PuppijetsTPt100dR08_ 1', 'i', -999),
                                   ('nAK4PuppijetsLPt150dR08_1', 'i', -999), ('nAK4PuppijetsMPt150dR08_1', 'i', -999),
                                   ('nAK4PuppijetsTPt150dR08_1', 'i', -999),
                                   ('nAK4PuppijetsLPt50dR08_2', 'i', -999), ('nAK4PuppijetsMPt50dR08_2', 'i', -999),
                                   ('nAK4PuppijetsTPt50dR08_2', 'i', -999),
                                   ('nAK4PuppijetsLPt100dR08_2', 'i', -999), ('nAK4PuppijetsMPt100dR08_2', 'i', -999),
                                   ('nAK4PuppijetsTPt100dR08_ 1', 'i', -999),
                                   ('nAK4PuppijetsLPt150dR08_2', 'i', -999), ('nAK4PuppijetsMPt150dR08_2', 'i', -999),
                                   ('nAK4PuppijetsTPt150dR08_2', 'i', -999),
                                   ('nAK4PuppijetsLPt150dR08_0', 'i', -999), ('nAK4PuppijetsMPt150dR08_0', 'i', -999),
                                   ('nAK4PuppijetsTPt150dR08_0', 'i', -999),
                                   ('AK4Puppijet3_pt', 'f', 0),('AK4Puppijet2_pt', 'f', 0), ('AK4Puppijet1_pt', 'f', 0),
                                   ('AK4Puppijet0_pt', 'f', 0),
                                   ('AK4Puppijet3_eta', 'f', 0), ('AK4Puppijet2_eta', 'f', 0),
                                   ('AK4Puppijet1_eta', 'f', 0), ('AK4Puppijet0_eta', 'f', 0)
                                   ])

        # AK8
        if not self._fillCA15:
            self._branches.extend([('AK8Puppijet0_msd', 'd', -999), ('AK8Puppijet0_pt', 'd', -999),
                          ('AK8Puppijet0_pt_JERUp', 'd', -999), ('AK8Puppijet0_pt_JERDown', 'd', -999),
                          ('AK8Puppijet0_pt_JESUp', 'd', -999), ('AK8Puppijet0_pt_JESDown', 'd', -999),
                          ('AK8Puppijet0_eta', 'd', -999), ('AK8Puppijet0_phi', 'd', -999),
                          ('AK8Puppijet0_tau21', 'd', -999), ('AK8Puppijet0_tau32', 'd', -999),
                          ('AK8Puppijet0_N2sdb1', 'd', -999), ('AK8Puppijet0_doublecsv', 'd', -999),
                          ('AK8Puppijet0_isTightVJet', 'i', 0)
                          ])
            if not self._minBranches:
                self._branches.extend([('AK8Puppijet1_pt', 'd', -999), ('AK8Puppijet2_pt', 'd', -999),
                                   ('AK8Puppijet1_tau21', 'd', -999), ('AK8Puppijet2_tau21', 'd', -999),
                                   ('AK8Puppijet1_msd', 'd', -999), ('AK8Puppijet2_msd', 'd', -999),
                                   ('AK8Puppijet1_doublecsv', 'd', -999), ('AK8Puppijet2_doublecsv', 'i', -999),
                                   ('AK8Puppijet1_isTightVJet', 'i', 0), ('AK8Puppijet2_isTightVJet', 'i', 0) 
                                   ])
        else:
            self._branches.extend([('CA15Puppijet0_msd', 'd', -999), ('CA15Puppijet0_pt', 'd', -999),
                          ('CA15Puppijet0_pt_JERUp', 'd', -999), ('CA15Puppijet0_pt_JERDown', 'd', -999),
                          ('CA15Puppijet0_pt_JESUp', 'd', -999), ('CA15Puppijet0_pt_JESDown', 'd', -999),
                          ('CA15Puppijet0_eta', 'd', -999), ('CA15Puppijet0_phi', 'd', -999),
                          ('CA15Puppijet0_tau21', 'd', -999), ('CA15Puppijet0_tau32', 'd', -999),
                          ('CA15Puppijet0_N2sdb1', 'd', -999,), ('CA15Puppijet0_doublesub', 'd', -999), 
                          ('CA15Puppijet0_isTightVJet', 'i', 0)
                          ])
            if not self._minBranches:
                self._branches.extend([('CA15Puppijet1_pt', 'd', -999), ('CA15Puppijet2_pt', 'd', -999),
                                   ('CA15Puppijet1_tau21', 'd', -999), ('CA15Puppijet2_tau21', 'd', -999),
                                   ('CA15Puppijet1_msd', 'd', -999), ('CA15Puppijet2_msd', 'd', -999),
                                   ('CA15Puppijet1_doublesub', 'd', -999), ('CA15Puppijet2_doublesub', 'i', -999),
                                   ('CA15Puppijet1_isTightVJet', 'i', 0), ('CA15Puppijet2_isTightVJet', 'i', 0) 
                                   ])


        if not self._isData:
            self._branches.extend([('genMuFromW', 'i', -999), ('genEleFromW', 'i', -999), ('genTauFromW', 'i', -999)])
            self._branches.extend(
                [('genVPt', 'f', -999), ('genVEta', 'f', -999), ('genVPhi', 'f', -999), ('genVMass', 'f', -999),
                 ('topPtWeight', 'f', -999), ('topPt', 'f', -999), ('antitopPt', 'f', -999)])

        self._tt.SetBranchStatus("*", 0)
        for branch in self._branches:
            self._tt.SetBranchStatus(branch[0], 1)
        for branch in self._branches:
            setattr(self, branch[0].replace(' ', ''), array.array(branch[1], [branch[2]]))
            self._tt.SetBranchAddress(branch[0], getattr(self, branch[0].replace(' ', '')))

        # x = array.array('d',[0])
        # self._tt.SetBranchAddress( "h_n_ak4", n_ak4  )

        if not self._fillCA15: 
            self._jet_type = "AK8"
            self._rhobins = 50
            self._lrhobin = -7
            self._hrhobin = -1
            self._lrhocut = -6.0
            self._hrhocut = -2.1 
        else: 
            self._jet_type = "CA15"
            self._rhobins = 42
            self._lrhobin = -5
            self._hrhobin = 0
            self._lrhocut = -4.7
            self._hrhocut = -1.0 


        # define histograms
        histos1d = {            
            'h_npv': ["h_" + self._name + "_npv", ";number of PV;", 100, 0, 100],
            'h_pt_mu_muCR4_N2': ["h_" + self._name + "_pt_mu_muCR4_N2", "; leading muon p_{T} (GeV);", 50, 30, 500],
            'h_eta_mu_muCR4_N2': ["h_" + self._name + "_eta_mu_muCR4_N2", "; leading muon #eta;", 50, -2.5, 2.5],
            'h_pt_muCR4_N2': ["h_" + self._name + "_pt_muCR4_N2", "; " + self._jet_type + " leading p_{T} (GeV);", 50, 300, 2100],
            'h_eta_muCR4_N2': ["h_" + self._name + "_eta_muCR4_N2", "; " + self._jet_type + " leading #eta;", 50, -3, 3],
            'h_dbtag_muCR4_N2': ["h_" + self._name + "_dbtag_muCR4_N2", "; p_{T}-leading double b-tag;", 40, -1, 1],
            'h_t21ddt_muCR4_N2': ["h_" + self._name + "_t21ddt_muCR4_N2", "; " + self._jet_type + " #tau_{21}^{DDT};", 25, 0, 1.5],
            'h_msd_topR6_N2_pass': ["h_" + self._name + "_msd_topR6_N2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_pass_JESUp': ["h_" + self._name + "_msd_topR6_N2_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_pass_JESDown': ["h_" + self._name + "_msd_topR6_N2_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_pass_JERUp': ["h_" + self._name + "_msd_topR6_N2_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_pass_JERDown': ["h_" + self._name + "_msd_topR6_N2_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_fail': ["h_" + self._name + "_msd_topR6_N2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_fail_JESUp': ["h_" + self._name + "_msd_topR6_N2_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_fail_JESDown': ["h_" + self._name + "_msd_topR6_N2_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_fail_JERUp': ["h_" + self._name + "_msd_topR6_N2_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_topR6_N2_fail_JERDown': ["h_" + self._name + "_msd_topR6_N2_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2': ["h_" + self._name + "_msd_muCR4_N2", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass': ["h_" + self._name + "_msd_muCR4_N2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_JESUp': ["h_" + self._name + "_msd_muCR4_N2_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_JESDown': ["h_" + self._name + "_msd_muCR4_N2_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_JERUp': ["h_" + self._name + "_msd_muCR4_N2_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_JERDown': ["h_" + self._name + "_msd_muCR4_N2_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_mutriggerUp': ["h_" + self._name + "_msd_muCR4_N2_pass_mutriggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_mutriggerDown': ["h_" + self._name + "_msd_muCR4_N2_pass_mutriggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_muidUp': ["h_" + self._name + "_msd_muCR4_N2_pass_muidUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_muidDown': ["h_" + self._name + "_msd_muCR4_N2_pass_muidDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_muisoUp': ["h_" + self._name + "_msd_muCR4_N2_pass_muisoUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_muisoDown': ["h_" + self._name + "_msd_muCR4_N2_pass_muisoDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_PuUp': ["h_" + self._name + "_msd_muCR4_N2_pass_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_pass_PuDown': ["h_" + self._name + "_msd_muCR4_N2_pass_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail': ["h_" + self._name + "_msd_muCR4_N2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_JESUp': ["h_" + self._name + "_msd_muCR4_N2_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_JESDown': ["h_" + self._name + "_msd_muCR4_N2_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_JERUp': ["h_" + self._name + "_msd_muCR4_N2_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_JERDown': ["h_" + self._name + "_msd_muCR4_N2_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_mutriggerUp': ["h_" + self._name + "_msd_muCR4_N2_fail_mutriggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_mutriggerDown': ["h_" + self._name + "_msd_muCR4_N2_fail_mutriggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_muidUp': ["h_" + self._name + "_msd_muCR4_N2_fail_muidUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_muidDown': ["h_" + self._name + "_msd_muCR4_N2_fail_muidDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_muisoUp': ["h_" + self._name + "_msd_muCR4_N2_fail_muisoUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_muisoDown': ["h_" + self._name + "_msd_muCR4_N2_fail_muisoDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_PuUp': ["h_" + self._name + "_msd_muCR4_N2_fail_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            'h_msd_muCR4_N2_fail_PuDown': ["h_" + self._name + "_msd_muCR4_N2_fail_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
        }
        if not self._minBranches:
            histos1d_ext = {
                'h_Cuts': ["h_" + self._name + "_Cuts", "; Cut ", 8, 0, 8],
                'h_Cuts_p': ["h_" + self._name + "_Cuts_p", "; Cut ", 8, 0, 8],
                'h_Cuts_muon': ["h_" + self._name + "_Cuts_muon", "; Cut ", 11, 0, 11],
                'h_Cuts_muon_p': ["h_" + self._name + "_Cuts_muon_p", "; Cut ", 11, 0, 11],
                'h_n_ak4': ["h_" + self._name + "_n_ak4", "; AK4 n_{jets}, p_{T} > 30 GeV;", 20, 0, 20],
                'h_ht': ["h_" + self._name + "_ht", "; HT (GeV);;", 50, 300, 2100],
                'h_pt_bbleading': ["h_" + self._name + "_pt_bbleading", "; " + self._jet_type + " leading p_{T} (GeV);", 50, 300, 2100],
                'h_bb_bbleading': ["h_" + self._name + "_bb_bbleading", "; double b-tag;", 40, -1, 1],
                'h_msd_bbleading': ["h_" + self._name + "_msd_bbleading", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 30, 40, 250],
                'h_n_ak4fwd': ["h_" + self._name + "_n_ak4fwd", "; AK4 n_{jets}, p_{T} > 30 GeV, 2.5<|#eta|<4.5;", 20, 0, 20],
                'h_n_ak4L': ["h_" + self._name + "_n_ak4L", "; AK4 n_{L b-tags}, #DeltaR > 0.8, p_{T} > 40 GeV;", 20, 0, 20],
                'h_n_ak4M': ["h_" + self._name + "_n_ak4M", "; AK4 n_{M b-tags}, #DeltaR > 0.8, p_{T} > 40 GeV;", 20, 0, 20],
                'h_n_ak4T': ["h_" + self._name + "_n_ak4T", "; AK4 n_{T b-tags}, #DeltaR > 0.8, p_{T} > 40 GeV;", 20, 0, 20],
                'h_n_ak4_dR0p8': ["h_" + self._name + "_n_ak4_dR0p8", "; AK4 n_{jets}, #DeltaR > 0.8, p_{T} > 30 GeV;", 20, 0, 20],
                'h_isolationCA15': ["h_" + self._name + "_isolationCA15", "; AK8/CA15 p_{T} ratio ;", 50, 0.5, 1.5],
                'h_met': ["h_" + self._name + "_met", "; E_{T}^{miss} (GeV) ;", 50, 0, 500],
                'h_pt': ["h_" + self._name + "_pt", "; " + self._jet_type + " leading p_{T} (GeV);", 50, 300, 2100],
                'h_eta': ["h_" + self._name + "_eta", "; " + self._jet_type + " leading #eta;", 50, -3, 3],
                'h_pt_sub1': ["h_" + self._name + "_pt_sub1", "; " + self._jet_type + " subleading p_{T} (GeV);", 50, 300, 2100],
                'h_pt_sub2': ["h_" + self._name + "_pt_sub2", "; " + self._jet_type + " 3rd leading p_{T} (GeV);", 50, 300, 2100],
                'h_pt_dbtagCut': ["h_" + self._name + "_pt_dbtagCut", "; " + self._jet_type + " leading p_{T} (GeV);", 45, 300, 2100],
                'h_msd': ["h_" + self._name + "_msd", "; p_{T}-leading m_{SD} (GeV);", 80, 40, 600],
                'h_msd_nocut': ["h_" + self._name + "_msd_nocut", "; p_{T}-leading m_{SD} (GeV);", 86, 0, 602],
                'h_rho': ["h_" + self._name + "_rho", "; p_{T}-leading  #rho=log(m_{SD}^{2}/p_{T}^{2}) ;", self._rhobins , self._lrhobin, self._hrhobin], 
                'h_rho_nocut': ["h_" + self._name + "_rho_nocut", "; p_{T}-leading  #rho=log(m_{SD}^{2}/p_{T}^{2}) ;", self._rhobins , self._lrhobin, self._hrhobin], 
                'h_msd_raw': ["h_" + self._name + "_msd_raw", "; " + self._jet_type + " m_{SD}^{PUPPI} no correction (GeV);", 80, 40, 600],
                'h_msd_raw_nocut': ["h_" + self._name + "_msd_raw_nocut", "; " + self._jet_type + " m_{SD}^{PUPPI} no correction (GeV);", 86, 0, 602],
                'h_msd_inc': ["h_" + self._name + "_msd_inc", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 100, 0, 500],
                'h_msd_dbtagCut': ["h_" + self._name + "_msd_dbtagCut", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_t21ddtCut': ["h_" + self._name + "_msd_t21ddtCut", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_t21ddtCut_inc': ["h_" + self._name + "_msd_t21ddtCut_inc", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 100, 0, 500],
                'h_msd_N2Cut': ["h_" + self._name + "_msd_N2Cut", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_dbtag': ["h_" + self._name + "_dbtag", "; p_{T}-leading double b-tag;", 40, -1, 1],
                'h_dbtag_sub1': ["h_" + self._name + "_dbtag_sub1", "; 2nd p_{T}-leading double b-tag;", 40, -1, 1],
                'h_dbtag_sub2': ["h_" + self._name + "_dbtag_sub2", "; 3rd p_{T}-leading double b-tag;", 40, -1, 1],
                'h_t21': ["h_" + self._name + "_t21", "; " + self._jet_type + " #tau_{21};", 25, 0, 1.5],
                'h_t21ddt': ["h_" + self._name + "_t21ddt", "; " + self._jet_type + " #tau_{21}^{DDT};", 25, 0, 1.5],
                'h_t32': ["h_" + self._name + "_t32", "; " + self._jet_type + " #tau_{32};", 25, 0, 1.5],
                'h_t32_t21ddtCut': ["h_" + self._name + "_t32_t21ddtCut", "; " + self._jet_type + " #tau_{32};", 20, 0, 1.5],
                'h_n2b1sd': ["h_" + self._name + "_n2b1sd", "; " + self._jet_type + " N_{2}^{1} (SD);", 50, -0.5, 1.5],
                'h_n2b1sd_norhocut': ["h_" + self._name + "_n2b1sd_norhocut", "; " + self._jet_type + " N_{2}^{1} (SD);", 50, -0.5, 1.5],
                'h_n2b1sdddt': ["h_" + self._name + "_n2b1sdddt", "; " + self._jet_type + " N_{2}^{1,DDT} (SD);", 25, -0.5, 0.5],
                'h_n2b1sdddt_norhocut': ["h_" + self._name + "_n2b1sdddt_norhocut", "; " + self._jet_type + " N_{2}^{1,DDT} (SD);", 25, -0.5, 0.5],
                'h_n2b1sdddt_aftercut': ["h_" + self._name + "_n2b1sdddt_aftercut", "; p_{T}-leading N_{2}^{1,DDT};", 25, -0.5, 0.5],
		'h_dbtag_aftercut': ["h_" + self._name + "_dbtag_aftercut", "; p_{T}-leading double-b tagger;", 33, -1, 1],
                'h_msd_raw_SR_fail': ["h_" + self._name + "_msd_raw_SR_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} no corr (GeV);", 80, 40, 600],
                'h_msd_raw_SR_pass': ["h_" + self._name + "_msd_raw_SR_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} no corr (GeV);", 80, 40, 600],
                'h_msd_topR6_pass': ["h_" + self._name + "_msd_topR6_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_pass_JESUp': ["h_" + self._name + "_msd_topR6_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_pass_JESDown': ["h_" + self._name + "_msd_topR6_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_pass_JERUp': ["h_" + self._name + "_msd_topR6_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_pass_JERDown': ["h_" + self._name + "_msd_topR6_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_fail': ["h_" + self._name + "_msd_topR6_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_fail_JESUp': ["h_" + self._name + "_msd_topR6_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_fail_JESDown': ["h_" + self._name + "_msd_topR6_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_fail_JERUp': ["h_" + self._name + "_msd_topR6_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_fail_JERDown': ["h_" + self._name + "_msd_topR6_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_n_ak4L100': ["h_" + self._name + "_n_ak4L100", "; AK4 n_{L b-tags}, #DeltaR > 0.8, p_{T} > 100 GeV;", 10, 0, 10],
                'h_n_ak4L150': ["h_" + self._name + "_n_ak4L150", "; AK4 n_{L b-tags}, #DeltaR > 0.8, p_{T} > 150 GeV;", 10, 0, 10],
                'h_n_ak4M100': ["h_" + self._name + "_n_ak4M100", "; AK4 n_{M b-tags}, #DeltaR > 0.8, p_{T} > 100 GeV;", 10, 0, 10],
                'h_n_ak4M150': ["h_" + self._name + "_n_ak4M150", "; AK4 n_{M b-tags}, #DeltaR > 0.8, p_{T} > 150 GeV;", 10, 0, 10],
                'h_n_ak4T100': ["h_" + self._name + "_n_ak4T100", "; AK4 n_{T b-tags}, #DeltaR > 0.8, p_{T} > 100 GeV;", 10, 0, 10],
                'h_n_ak4T150': ["h_" + self._name + "_n_ak4T150", "; AK4 n_{T b-tags}, #DeltaR > 0.8, p_{T} > 150 GeV;", 10, 0, 10],
                'h_msd_muCR1': ["h_" + self._name + "_msd_muCR1", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR2': ["h_" + self._name + "_msd_muCR2", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR3': ["h_" + self._name + "_msd_muCR3", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_pt_mu_muCR4': ["h_" + self._name + "_pt_mu_muCR4", "; leading muon p_{T} (GeV);", 50, 30, 500],
                'h_eta_mu_muCR4': ["h_" + self._name + "_eta_mu_muCR4", "; leading muon #eta;", 50, -2.5, 2.5],
                'h_pt_muCR4': ["h_" + self._name + "_pt_muCR4", "; " + self._jet_type + " leading p_{T} (GeV);", 50, 300, 2100],
                'h_eta_muCR4': ["h_" + self._name + "_eta_muCR4", "; " + self._jet_type + " leading #eta;", 50, -3, 3],
                'h_dbtag_muCR4': ["h_" + self._name + "_dbtag_muCR4", "; p_{T}-leading double b-tag;", 40, -1, 1],
                'h_t21ddt_muCR4': ["h_" + self._name + "_t21ddt_muCR4", "; " + self._jet_type + " #tau_{21}^{DDT};", 25, 0, 1.5],
                'h_msd_muCR4': ["h_" + self._name + "_msd_muCR4", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass': ["h_" + self._name + "_msd_muCR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_JESUp': ["h_" + self._name + "_msd_muCR4_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_JESDown': ["h_" + self._name + "_msd_muCR4_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_JERUp': ["h_" + self._name + "_msd_muCR4_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_JERDown': ["h_" + self._name + "_msd_muCR4_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_mutriggerUp': ["h_" + self._name + "_msd_muCR4_pass_mutriggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_mutriggerDown': ["h_" + self._name + "_msd_muCR4_pass_mutriggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_muidUp': ["h_" + self._name + "_msd_muCR4_pass_muidUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_muidDown': ["h_" + self._name + "_msd_muCR4_pass_muidDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_muisoUp': ["h_" + self._name + "_msd_muCR4_pass_muisoUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_muisoDown': ["h_" + self._name + "_msd_muCR4_pass_muisoDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_PuUp': ["h_" + self._name + "_msd_muCR4_pass_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_pass_PuDown': ["h_" + self._name + "_msd_muCR4_pass_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail': ["h_" + self._name + "_msd_muCR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_JESUp': ["h_" + self._name + "_msd_muCR4_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_JESDown': ["h_" + self._name + "_msd_muCR4_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_JERUp': ["h_" + self._name + "_msd_muCR4_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_JERDown': ["h_" + self._name + "_msd_muCR4_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_mutriggerUp': ["h_" + self._name + "_msd_muCR4_fail_mutriggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_mutriggerDown': ["h_" + self._name + "_msd_muCR4_fail_mutriggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_muidUp': ["h_" + self._name + "_msd_muCR4_fail_muidUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_muidDown': ["h_" + self._name + "_msd_muCR4_fail_muidDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_muisoUp': ["h_" + self._name + "_msd_muCR4_fail_muisoUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_muisoDown': ["h_" + self._name + "_msd_muCR4_fail_muisoDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_PuUp': ["h_" + self._name + "_msd_muCR4_fail_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_fail_PuDown': ["h_" + self._name + "_msd_muCR4_fail_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR5': ["h_" + self._name + "_msd_muCR5", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR6': ["h_" + self._name + "_msd_muCR6", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_bbleading_muCR4_pass': ["h_" + self._name + "_msd_bbleading_muCR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_bbleading_muCR4_fail': ["h_" + self._name + "_msd_bbleading_muCR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR1': ["h_" + self._name + "_msd_topR1", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR2_pass': ["h_" + self._name + "_msd_topR2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR3_pass': ["h_" + self._name + "_msd_topR3_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR4_pass': ["h_" + self._name + "_msd_topR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR5_pass': ["h_" + self._name + "_msd_topR5_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR2_fail': ["h_" + self._name + "_msd_topR2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR3_fail': ["h_" + self._name + "_msd_topR3_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR5_fail': ["h_" + self._name + "_msd_topR5_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR7_pass': ["h_" + self._name + "_msd_topR7_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR7_fail': ["h_" + self._name + "_msd_topR7_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR4_fail': ["h_" + self._name + "_msd_topR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_bbleading_topR6_pass': ["h_" + self._name + "_msd_bbleading_topR6_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_bbleading_topR6_fail': ["h_" + self._name + "_msd_bbleading_topR6_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            }
            dbcuts = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
            for dbcut in dbcuts:
                dbcutstring = str(dbcut).replace('0.','p')
                histos1d_ext.update({
                'h_msd_topR6_%s_pass'%dbcutstring: ["h_" + self._name + "_msd_topR6_%s_pass"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_%s_fail'%dbcutstring: ["h_" + self._name + "_msd_topR6_%s_fail"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_N2_%s_pass'%dbcutstring: ["h_" + self._name + "_msd_topR6_N2_%s_pass"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_topR6_N2_%s_fail'%dbcutstring: ["h_" + self._name + "_msd_topR6_N2_%s_fail"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_JESUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_JESDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_JERUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_JERDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_mutriggerUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_mutriggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_mutriggerDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_mutriggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_muidUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_muidUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_muidDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_muidDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_muisoUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_muisoUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_muisoDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_muisoDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_PuUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_pass_PuDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_pass_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_JESUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_JESDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_JERUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_JERDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_mutriggerUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_mutriggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_mutriggerDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_mutriggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_muidUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_muidUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_muidDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_muidDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_muisoUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_muisoUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_muisoDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_muisoDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_PuUp'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
                'h_msd_muCR4_N2_%s_fail_PuDown'%dbcutstring: ["h_" + self._name + "_msd_muCR4_N2_%s_fail_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV);", 80, 40, 600],
            })
            histos1d = dict(histos1d.items() + histos1d_ext.items() )

        msd_binBoundaries = []
        for i in range(0, 81):
            msd_binBoundaries.append(40. + i * 7)
        print(msd_binBoundaries)
        pt_binBoundaries = [450, 500, 550, 600, 675, 800, 1000]

        histos2d_fix = {
            'h_rhop_v_t21': ["h_" + self._name + "_rhop_v_t21", "; " + self._jet_type + " rho^{DDT}; " + self._jet_type + " <#tau_{21}>", 15, -5, 10, 25, 0, 1.5]
        }

        histos2d = {
            'h_msd_v_pt_topR6_N2_pass': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_JESUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_JESDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_JERUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_JERDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_triggerUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_triggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_triggerDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_triggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_PuUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_PuDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_pass_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_matched': ["h_" + self._name + "_msd_v_pt_N2_topR6_pass_matched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_pass_unmatched': ["h_" + self._name + "_msd_v_pt_N2_topR6_pass_unmatched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_JESUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_JESDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_JERUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_JERDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_triggerUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_triggerUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_triggerDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_triggerDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_PuUp': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_PuUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_PuDown': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_PuDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_matched': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_matched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_topR6_N2_fail_unmatched': ["h_" + self._name + "_msd_v_pt_topR6_N2_fail_unmatched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_muCR4_N2_pass': ["h_" + self._name + "_msd_v_pt_muCR4_N2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            'h_msd_v_pt_muCR4_N2_fail': ["h_" + self._name + "_msd_v_pt_muCR4_N2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"]
        }

        if not self._minBranches:
            histos2d_ext = {
                'h_msd_v_pt_topR1': ["h_" + self._name + "_msd_v_pt_topR1", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR2_pass': ["h_" + self._name + "_msd_v_pt_topR2_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR3_pass': ["h_" + self._name + "_msd_v_pt_topR3_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR4_pass': ["h_" + self._name + "_msd_v_pt_topR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR5_pass': ["h_" + self._name + "_msd_v_pt_topR5_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass': ["h_" + self._name + "_msd_v_pt_topR6_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_JESUp': ["h_" + self._name + "_msd_v_pt_topR6_pass_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_JESDown': ["h_" + self._name + "_msd_v_pt_topR6_pass_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_JERUp': ["h_" + self._name + "_msd_v_pt_topR6_pass_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_JERDown': ["h_" + self._name + "_msd_v_pt_topR6_pass_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_matched': ["h_" + self._name + "_msd_v_pt_topR6_pass_matched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_pass_unmatched': ["h_" + self._name + "_msd_v_pt_topR6_pass_unmatched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_matched': ["h_" + self._name + "_msd_v_pt_topR6_fail_matched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_unmatched': ["h_" + self._name + "_msd_v_pt_topR6_fail_unmatched", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR7_pass': ["h_" + self._name + "_msd_v_pt_topR7_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR2_fail': ["h_" + self._name + "_msd_v_pt_topR2_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR3_fail': ["h_" + self._name + "_msd_v_pt_topR3_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR4_fail': ["h_" + self._name + "_msd_v_pt_topR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR5_fail': ["h_" + self._name + "_msd_v_pt_topR5_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail': ["h_" + self._name + "_msd_v_pt_topR6_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_JESUp': ["h_" + self._name + "_msd_v_pt_topR6_fail_JESUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_JESDown': ["h_" + self._name + "_msd_v_pt_topR6_fail_JESDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_JERUp': ["h_" + self._name + "_msd_v_pt_topR6_fail_JERUp", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_fail_JERDown': ["h_" + self._name + "_msd_v_pt_topR6_fail_JERDown", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_raw_fail': ["h_" + self._name + "_msd_v_pt_topR6_raw_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_raw_pass': ["h_" + self._name + "_msd_v_pt_topR6_raw_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR7_fail': ["h_" + self._name + "_msd_v_pt_topR7_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_bbleading_topR6_pass': ["h_" + self._name + "_msd_v_pt_bbleading_topR6_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_bbleading_topR6_fail': ["h_" + self._name + "_msd_v_pt_bbleading_topR6_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_muCR4_pass': ["h_" + self._name + "_msd_v_pt_muCR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_muCR4_fail': ["h_" + self._name + "_msd_v_pt_muCR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_bbleading_muCR4_pass': ["h_" + self._name + "_msd_v_pt_bbleading_muCR4_pass", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_bbleading_muCR4_fail': ["h_" + self._name + "_msd_v_pt_bbleading_muCR4_fail", "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
            }
            dbcuts = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
            for dbcut in dbcuts:
                dbcutstring = str(dbcut).replace('0.','p')
                histos2d_ext.update({
                'h_msd_v_pt_topR6_%s_fail'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_matched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_matched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_unmatched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_unmatched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_JERUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_JERDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_JESUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_JESDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_triggerUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_triggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_triggerDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_triggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_PuUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_fail_PuDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_fail_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_matched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_matched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_unmatched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_unmatched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_JERUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_JERDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_JESUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_JESDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_triggerUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_triggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_triggerDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_triggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_PuUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_%s_pass_PuDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_%s_pass_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_matched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_matched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_unmatched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_unmatched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_JERUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_JERDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_JESUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_JESDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_triggerUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_triggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_triggerDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_triggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_PuUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_fail_PuDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_fail_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_matched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_matched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_unmatched'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_unmatched"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_JERUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_JERUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_JERDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_JERDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_JESUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_JESUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_JESDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_JESDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_triggerUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_triggerUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_triggerDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_triggerDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_PuUp'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_PuUp"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"],
                'h_msd_v_pt_topR6_N2_%s_pass_PuDown'%dbcutstring: ["h_" + self._name + "_msd_v_pt_topR6_N2_%s_pass_PuDown"%dbcutstring, "; " + self._jet_type + " m_{SD}^{PUPPI} (GeV); " + self._jet_type + " p_{T} (GeV)"]
            })


            histos2d = dict(histos2d.items() + histos2d_ext.items())

        for key, val in histos1d.iteritems():
            setattr(self, key, ROOT.TH1F(val[0], val[1], val[2], val[3], val[4]))
            (getattr(self, key)).Sumw2()
        for key, val in histos2d_fix.iteritems():
            setattr(self, key, ROOT.TH2F(val[0], val[1], val[2], val[3], val[4], val[5], val[6], val[7]))
            (getattr(self, key)).Sumw2()
        for key, val in histos2d.iteritems():
            tmp = ROOT.TH2F(val[0], val[1], len(msd_binBoundaries) - 1, array.array('d', msd_binBoundaries),
                            len(pt_binBoundaries) - 1, array.array('d', pt_binBoundaries))
            setattr(self, key, tmp)
            (getattr(self, key)).Sumw2()

        # loop
        if len(fn) > 0:
            self.loop()

    def loop(self):
        # looping
        nent = self._tt.GetEntries()
        print "\n", "***********************************************************************************************************************************"
        print self._name
        print "***********************************************************************************************************************************", "\n"
        print nent , "\n"        
        cut = []
        cut = [0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]
        cut_muon = []
        cut_muon = [0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.]

        self._tt.SetNotify(self._cutFormula)
        for i in xrange(nent):
            if i % self._sf != 0: continue

            # self._tt.LoadEntry(i)
            self._tt.LoadTree(i)
            selected = False
            for j in range(self._cutFormula.GetNdata()):
                if (self._cutFormula.EvalInstance(j)):
                    selected = True
                    break
            if not selected: continue

            self._tt.GetEntry(i)

            if (nent / 100 > 0 and i % (1 * nent / 100) == 0):
                sys.stdout.write("\r[" + "=" * int(20 * i / nent) + " " + str(round(100. * i / nent, 0)) + "% done")
                sys.stdout.flush()

            puweight = self.puWeight[0] #corrected
            nPuForWeight = min(self.npu[0], 49.5)
	    #$print(puweight,self._puw.GetBinContent(self._puw.FindBin(nPuForWeight)))
            #puweight = self._puw.GetBinContent(self._puw.FindBin(nPuForWeight))
            puweight_up = self._puw_up.GetBinContent(self._puw_up.FindBin(nPuForWeight))
            puweight_down = self._puw_down.GetBinContent(self._puw_down.FindBin(nPuForWeight))
            # print(self.puWeight[0],puweight,puweight_up,puweight_down)
            fbweight = self.scale1fb[0] * self._lumi
            # if self._name=='tqq' or 'TTbar' in self._name:
            #    fbweight = fbweight/self.topPtWeight[0] # remove top pt reweighting (assuming average weight is ~ 1)
            vjetsKF = 1.
	    wscale=[1.0,1.0,1.0,1.20,1.25,1.25,1.0]
	    ptscale=[0, 500, 600, 700, 800, 900, 1000,3000]
	    ptKF=1.
            if self._name == 'wqq' or self._name == 'W':
                # print self._name
		for i in range(0, len(ptscale)):
			if self.genVPt[0] > ptscale[i] and self.genVPt[0]<ptscale[i+1]:  ptKF=wscale[i]
                vjetsKF = self.kfactor[0] * 1.35 * ptKF  # ==1 for not V+jets events
            elif self._name == 'zqq' or self._name == 'DY':
                # print self._name
                vjetsKF = self.kfactor[0] * 1.45  # ==1 for not V+jets events
            # trigger weight
            if not self._fillCA15: 
                massForTrig = min(self.AK8Puppijet0_msd[0], 300.)
                ptForTrig = max(200., min(self.AK8Puppijet0_pt[0], 1000.))
            else: 
                massForTrig = min(self.CA15Puppijet0_msd[0], 300.)
                ptForTrig = max(200., min(self.CA15Puppijet0_pt[0], 1000.))
            trigweight = self._trig_eff.GetEfficiency(self._trig_eff.FindFixBin(massForTrig, ptForTrig))
            trigweightUp = trigweight + self._trig_eff.GetEfficiencyErrorUp(
                self._trig_eff.FindFixBin(massForTrig, ptForTrig))
            trigweightDown = trigweight - self._trig_eff.GetEfficiencyErrorLow(
                self._trig_eff.FindFixBin(massForTrig, ptForTrig))
            if trigweight <= 0 or trigweightDown <= 0 or trigweightUp <= 0:
                print 'trigweights are %f, %f, %f, setting all to 1' % (trigweight, trigweightUp, trigweightDown)
                trigweight = 1
                trigweightDown = 1
                trigweightUp = 1

            weight = puweight * fbweight * self._sf * vjetsKF * trigweight
            weight_triggerUp = puweight * fbweight * self._sf * vjetsKF * trigweightUp
            weight_triggerDown = puweight * fbweight * self._sf * vjetsKF * trigweightDown
            weight_pu_up = puweight_up * fbweight * self._sf * vjetsKF * trigweight
            weight_pu_down = puweight_down * fbweight * self._sf * vjetsKF * trigweight

            mutrigweight = 1
            mutrigweightDown = 1
            mutrigweightUp = 1
            if self.nmuLoose[0] > 0:
                muPtForTrig = max(52., min(self.vmuoLoose0_pt[0], 700.))
                muEtaForTrig = min(abs(self.vmuoLoose0_eta[0]), 2.3)
                mutrigweight = self._mutrig_eff.GetBinContent(self._mutrig_eff.FindBin(muPtForTrig, muEtaForTrig))
                mutrigweightUp = mutrigweight + self._mutrig_eff.GetBinError(
                    self._mutrig_eff.FindBin(muPtForTrig, muEtaForTrig))
                mutrigweightDown = mutrigweight - self._mutrig_eff.GetBinError(
                    self._mutrig_eff.FindBin(muPtForTrig, muEtaForTrig))
                if mutrigweight <= 0 or mutrigweightDown <= 0 or mutrigweightUp <= 0:
                    print 'mutrigweights are %f, %f, %f, setting all to 1' % (
                    mutrigweight, mutrigweightUp, mutrigweightDown)
                    mutrigweight = 1
                    mutrigweightDown = 1
                    mutrigweightUp = 1

            muidweight = 1
            muidweightDown = 1
            muidweightUp = 1
            if self.nmuLoose[0] > 0:
                muPtForId = max(20., min(self.vmuoLoose0_pt[0], 100.))
                muEtaForId = min(abs(self.vmuoLoose0_eta[0]), 2.3)
                muidweight = self._muid_eff.GetBinContent(self._muid_eff.FindBin(muPtForId, muEtaForId))
                muidweightUp = muidweight + self._muid_eff.GetBinError(self._muid_eff.FindBin(muPtForId, muEtaForId))
                muidweightDown = muidweight - self._muid_eff.GetBinError(self._muid_eff.FindBin(muPtForId, muEtaForId))
                if muidweight <= 0 or muidweightDown <= 0 or muidweightUp <= 0:
                    print 'muidweights are %f, %f, %f, setting all to 1' % (muidweight, muidweightUp, muidweightDown)
                    muidweight = 1
                    muidweightDown = 1
                    muidweightUp = 1

            muisoweight = 1
            muisoweightDown = 1
            muisoweightUp = 1
            if self.nmuLoose[0] > 0:
                muPtForIso = max(20., min(self.vmuoLoose0_pt[0], 100.))
                muEtaForIso = min(abs(self.vmuoLoose0_eta[0]), 2.3)
                muisoweight = self._muiso_eff.GetBinContent(self._muiso_eff.FindBin(muPtForIso, muEtaForIso))
                muisoweightUp = muisoweight + self._muiso_eff.GetBinError(
                    self._muiso_eff.FindBin(muPtForIso, muEtaForIso))
                muisoweightDown = muisoweight - self._muiso_eff.GetBinError(
                    self._muiso_eff.FindBin(muPtForIso, muEtaForIso))
                if muisoweight <= 0 or muisoweightDown <= 0 or muisoweightUp <= 0:
                    print 'muisoweights are %f, %f, %f, setting all to 1' % (
                    muisoweight, muisoweightUp, muisoweightDown)
                    muisoweight = 1
                    muisoweightDown = 1
                    muisoweightUp = 1

            weight_mu = puweight * fbweight * self._sf * vjetsKF * mutrigweight * muidweight * muisoweight
            weight_mutriggerUp = puweight * fbweight * self._sf * vjetsKF * mutrigweightUp * muidweight * muisoweight
            weight_mutriggerDown = puweight * fbweight * self._sf * vjetsKF * mutrigweightDown * muidweight * muisoweight
            weight_muidUp = puweight * fbweight * self._sf * vjetsKF * mutrigweight * muidweightUp * muisoweight
            weight_muidDown = puweight * fbweight * self._sf * vjetsKF * mutrigweight * muidweightDown * muisoweight
            weight_muisoUp = puweight * fbweight * self._sf * vjetsKF * mutrigweight * muidweight * muisoweightUp
            weight_muisoDown = puweight * fbweight * self._sf * vjetsKF * mutrigweight * muidweight * muisoweightDown
            weight_mu_pu_up = puweight_up * fbweight * self._sf * vjetsKF * mutrigweight * muidweight * muisoweight
            weight_mu_pu_down = puweight_down * fbweight * self._sf * vjetsKF * mutrigweight * muidweight * muisoweight

            if self._isData:
                weight = 1
                weight_triggerUp = 1
                weight_triggerDown = 1
                weight_pu_up = 1
                weight_pu_down = 1
                weight_mu = 1
                weight_mutriggerUp = 1
                weight_mutriggerDown = 1
                weight_muidUp = 1
                weight_muidDown = 1
                weight_muisoUp = 1
                weight_muisoDown = 1
                weight_mu_pu_up = 1
                weight_mu_pu_down = 1

            if not self._fillCA15:                              #AK8 info
                jmsd_raw = self.AK8Puppijet0_msd[0]
                jpt = self.AK8Puppijet0_pt[0]
                jpt_JERUp = self.AK8Puppijet0_pt_JERUp[0]
                jpt_JERDown = self.AK8Puppijet0_pt_JERDown[0]
                jpt_JESUp = self.AK8Puppijet0_pt_JESUp[0]
                jpt_JESDown = self.AK8Puppijet0_pt_JESDown[0]
                #print "AK8", jpt, jpt_JESUp, jpt_JESDown, jpt_JERUp, jpt_JERDown
                jeta = self.AK8Puppijet0_eta[0]
                jmsd = self.AK8Puppijet0_msd[0] * self.PUPPIweight(jpt, jeta)
                jphi = self.AK8Puppijet0_phi[0]
                if not self._minBranches:
                    jpt_sub1 = self.AK8Puppijet1_pt[0]
                    jpt_sub2 = self.AK8Puppijet2_pt[0]
                jt21 = self.AK8Puppijet0_tau21[0]
                jt32 = self.AK8Puppijet0_tau32[0]
                jtN2b1sd = self.AK8Puppijet0_N2sdb1[0]
            else:                                               #CA15 info
                jmsd_raw = self.CA15Puppijet0_msd[0]
                jpt = self.CA15Puppijet0_pt[0]
                jpt_JERUp = self.CA15Puppijet0_pt_JERUp[0]
                jpt_JERDown = self.CA15Puppijet0_pt_JERDown[0]
                jpt_JESUp = self.CA15Puppijet0_pt_JESUp[0]
                jpt_JESDown = self.CA15Puppijet0_pt_JESDown[0]
                #print "CA15", jpt, jpt_JESUp, jpt_JESDown, jpt_JERUp, jpt_JERDown
                jeta = self.CA15Puppijet0_eta[0]
                jmsd = self.CA15Puppijet0_msd[0] * self.PUPPIweight(jpt, jeta)
                jphi = self.CA15Puppijet0_phi[0]
                if not self._minBranches:
                    jpt_sub1 = self.CA15Puppijet1_pt[0]
                    jpt_sub2 = self.CA15Puppijet2_pt[0]
                jt21 = self.CA15Puppijet0_tau21[0]
                jt32 = self.CA15Puppijet0_tau32[0]
                jtN2b1sd = self.CA15Puppijet0_N2sdb1[0]
            if jmsd <= 0: jmsd = 0.01
            rh = math.log(jmsd * jmsd / jpt / jpt)  
            rhP = math.log(jmsd * jmsd / jpt)
            jt21P = jt21 + 0.063 * rhP

            # N2DDT transformation
            cur_rho_index = self._trans_h2ddt.GetXaxis().FindBin(rh)
            cur_pt_index = self._trans_h2ddt.GetYaxis().FindBin(jpt)
            if rh > self._trans_h2ddt.GetXaxis().GetBinUpEdge(
                self._trans_h2ddt.GetXaxis().GetNbins()): cur_rho_index = self._trans_h2ddt.GetXaxis().GetNbins()
            if rh < self._trans_h2ddt.GetXaxis().GetBinLowEdge(1): cur_rho_index = 1
            if jpt > self._trans_h2ddt.GetYaxis().GetBinUpEdge(
                self._trans_h2ddt.GetYaxis().GetNbins()): cur_pt_index = self._trans_h2ddt.GetYaxis().GetNbins()
            if jpt < self._trans_h2ddt.GetYaxis().GetBinLowEdge(1): cur_pt_index = 1
            jtN2b1sdddt = jtN2b1sd - self._trans_h2ddt.GetBinContent(cur_rho_index, cur_pt_index)

            if not self._fillCA15:                                 #AK8 info
                jdb = self.AK8Puppijet0_doublecsv[0]
                if not self._minBranches:
                    if self.AK8Puppijet1_doublecsv[0] > 1:
                        jdb_sub1 = -99
                    else:
                        jdb_sub1 = self.AK8Puppijet1_doublecsv[0]
                    if self.AK8Puppijet2_doublecsv[0] > 1:
                        jdb_sub2 = -99
                    else:
                        jdb_sub2 = self.AK8Puppijet2_doublecsv[0]

            else:                                                 #CA15 info
                jdb = self.CA15Puppijet0_doublesub[0]
                if not self._minBranches:
                    if self.CA15Puppijet1_doublesub[0] > 1:
                        jdb_sub1 = -99
                    else:
                        jdb_sub1 = self.CA15Puppijet1_doublesub[0]
                    if self.CA15Puppijet2_doublesub[0] > 1:
                        jdb_sub2 = -99
                    else:
                        jdb_sub2 = self.CA15Puppijet2_doublesub[0]

            n_4 = self.nAK4PuppijetsPt30[0]
            if not self._minBranches:
                n_fwd_4 = self.nAK4PuppijetsfwdPt30[0]
            n_dR0p8_4 = self.nAK4PuppijetsPt30dR08_0[0]
            # due to bug, don't use jet counting JER/JES Up/Down for now
            # n_dR0p8_4_JERUp = self.nAK4PuppijetsPt30dR08jerUp_0[0]
            # n_dR0p8_4_JERDown = self.nAK4PuppijetsPt30dR08jerDown_0[0]
            # n_dR0p8_4_JESUp = self.nAK4PuppijetsPt30dR08jesUp_0[0]
            # n_dR0p8_4_JESDown = self.nAK4PuppijetsPt30dR08jesDown_0[0]
            n_dR0p8_4_JERUp = n_dR0p8_4
            n_dR0p8_4_JERDown = n_dR0p8_4
            n_dR0p8_4_JESUp = n_dR0p8_4
            n_dR0p8_4_JESDown = n_dR0p8_4
            
            n_MdR0p8_4 = self.nAK4PuppijetsMPt50dR08_0[0]
            if not self._minBranches:
                n_LdR0p8_4 = self.nAK4PuppijetsLPt50dR08_0[0]
                n_TdR0p8_4 = self.nAK4PuppijetsTPt50dR08_0[0]
                n_LPt100dR0p8_4 = self.nAK4PuppijetsLPt100dR08_0[0]
                n_MPt100dR0p8_4 = self.nAK4PuppijetsMPt100dR08_0[0]
                n_TPt100dR0p8_4 = self.nAK4PuppijetsTPt100dR08_0[0]
                n_LPt150dR0p8_4 = self.nAK4PuppijetsLPt150dR08_0[0]
                n_MPt150dR0p8_4 = self.nAK4PuppijetsMPt150dR08_0[0]
                n_TPt150dR0p8_4 = self.nAK4PuppijetsTPt150dR08_0[0]

            met = self.pfmet[0]#puppet[0]
            metphi = self.pfmetphi[0]#puppetphi[0]
            met_x = met * ROOT.TMath.Cos(metphi)
            met_y = met * ROOT.TMath.Sin(metphi)
            met_JESUp = ROOT.TMath.Sqrt(
                (met_x + self.MetXCorrjesUp[0]) * (met_x + self.MetXCorrjesUp[0]) + (met_y + self.MetYCorrjesUp[0]) * (
                met_y + self.MetYCorrjesUp[0]))
            met_JESDown = ROOT.TMath.Sqrt((met_x + self.MetXCorrjesDown[0]) * (met_x + self.MetXCorrjesDown[0]) + (
            met_y + self.MetYCorrjesDown[0]) * (met_y + self.MetYCorrjesDown[0]))
            met_JERUp = ROOT.TMath.Sqrt(
                (met_x + self.MetXCorrjerUp[0]) * (met_x + self.MetXCorrjerUp[0]) + (met_y + self.MetYCorrjerUp[0]) * (
                met_y + self.MetYCorrjerUp[0]))
            met_JERDown = ROOT.TMath.Sqrt((met_x + self.MetXCorrjerDown[0]) * (met_x + self.MetXCorrjerDown[0]) + (
            met_y + self.MetYCorrjerDown[0]) * (met_y + self.MetYCorrjerDown[0]))

            #print "MET", met, met_JESUp, met_JESDown, met_JERUp, met_JERDown
            ratioCA15_04 = self.AK8Puppijet0_ratioCA15_04[0]

            ntau = self.ntau[0]
            nmuLoose = self.nmuLoose[0]
            neleLoose = self.neleLoose[0]
            nphoLoose = self.nphoLoose[0]
            if not self._fillCA15: isTightVJet = self.AK8Puppijet0_isTightVJet[0]
            else: isTightVJet = self.CA15Puppijet0_isTightVJet[0]

            # muon info
            vmuoLoose0_pt = self.vmuoLoose0_pt[0]
            vmuoLoose0_eta = self.vmuoLoose0_eta[0]
            vmuoLoose0_phi = self.vmuoLoose0_phi[0]

            self.h_npv.Fill(self.npv[0], weight)

            # gen-matching for scale/smear systematic
            dphi = 9999.
            dpt = 9999.
            dmass = 9999.
            if (not self._isData):
                genVPt = self.genVPt[0]
                genVEta = self.genVEta[0]
                genVPhi = self.genVPhi[0]
                genVMass = self.genVMass[0]
                if genVPt > 0 and genVMass > 0:
                    dphi = math.fabs(delta_phi(genVPhi, jphi))
                    dpt = math.fabs(genVPt - jpt) / genVPt
                    dmass = math.fabs(genVMass - jmsd) / genVMass

            # Single Muon Control Regions
            if not self._minBranches:
                if jpt > PTCUTMUCR:
                    cut_muon[0] = cut_muon[0] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT:
                    cut_muon[1] = cut_muon[1] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1:
                    cut_muon[2] = cut_muon[2] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0:
                    cut_muon[3] = cut_muon[3] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0:
                    cut_muon[4] = cut_muon[4] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1:
                    cut_muon[5] = cut_muon[5] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1 and vmuoLoose0_pt > MUONPTCUT:
                    cut_muon[6] = cut_muon[6] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1:
                    cut_muon[7] = cut_muon[7] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3.:
                    cut_muon[8] = cut_muon[8] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3. and n_MdR0p8_4 >=1:
                    cut_muon[9] = cut_muon[9] + 1
                if jpt > PTCUTMUCR and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and ntau == 0 and nmuLoose == 1 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3. and n_MdR0p8_4 >=1 and jtN2b1sdddt < 0:
                    cut_muon[10] = cut_muon[10] + 1
            if jpt > PTCUTMUCR and jmsd > MASSCUT and nmuLoose == 1 and neleLoose == 0 and ntau == 0 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and isTightVJet==1 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3. and n_MdR0p8_4 >= 1:
                if not self._minBranches:
                    ht_ = 0.
                    if (abs(self.AK4Puppijet0_eta[0]) < 2.4 and self.AK4Puppijet0_pt[0] > 30): ht_ = ht_ + self.AK4Puppijet0_pt[0]
                    if (abs(self.AK4Puppijet1_eta[0]) < 2.4 and self.AK4Puppijet1_pt[0] > 30): ht_ = ht_ + self.AK4Puppijet1_pt[0]
                    if (abs(self.AK4Puppijet2_eta[0]) < 2.4 and self.AK4Puppijet2_pt[0] > 30): ht_ = ht_ + self.AK4Puppijet2_pt[0]
                    if (abs(self.AK4Puppijet3_eta[0]) < 2.4 and self.AK4Puppijet3_pt[0] > 30): ht_ = ht_ + self.AK4Puppijet3_pt[0]
                    self.h_ht.Fill(ht_, weight)
                    self.h_msd_muCR1.Fill(jmsd, weight_mu)
                    if jdb > DBTAGCUT:
                        self.h_msd_muCR2.Fill(jmsd, weight_mu)
                    if jt21P < 0.4:
                        self.h_msd_muCR3.Fill(jmsd, weight_mu)

                    self.h_t21ddt_muCR4.Fill(jt21P, weight_mu)
                    if jt21P < T21DDTCUT:
                        self.h_dbtag_muCR4.Fill(jdb, weight_mu)
                        self.h_msd_muCR4.Fill(jmsd, weight_mu)
                        self.h_pt_muCR4.Fill(jpt, weight_mu)
                        self.h_eta_muCR4.Fill(jeta, weight_mu)
                        self.h_pt_mu_muCR4.Fill(vmuoLoose0_pt, weight_mu)
                        self.h_eta_mu_muCR4.Fill(vmuoLoose0_eta, weight_mu)
                        if jdb > DBTAGCUT:
                            self.h_msd_muCR4_pass.Fill(jmsd, weight_mu)
                            self.h_msd_v_pt_muCR4_pass.Fill(jmsd, jpt, weight_mu)
                        elif jdb > self.DBTAGCUTMIN:
                            self.h_msd_muCR4_fail.Fill(jmsd, weight_mu)
                            self.h_msd_v_pt_muCR4_fail.Fill(jmsd, jpt, weight_mu)

                    if jdb > 0.7 and jt21P < 0.4:
                        self.h_msd_muCR5.Fill(jmsd, weight_mu)
                    if jdb > 0.7 and jt21P < T21DDTCUT:
                        self.h_msd_muCR6.Fill(jmsd, weight_mu)

                if jtN2b1sdddt < 0:
                    self.h_dbtag_muCR4_N2.Fill(jdb, weight_mu)
                    self.h_msd_muCR4_N2.Fill(jmsd, weight_mu)
                    self.h_pt_muCR4_N2.Fill(jpt, weight_mu)
                    self.h_eta_muCR4_N2.Fill(jeta, weight_mu)
                    self.h_pt_mu_muCR4_N2.Fill(vmuoLoose0_pt, weight_mu)
                    self.h_eta_mu_muCR4_N2.Fill(vmuoLoose0_eta, weight_mu)
                    if jdb > DBTAGCUT:
                        self.h_msd_muCR4_N2_pass.Fill(jmsd, weight_mu)
                        self.h_msd_v_pt_muCR4_N2_pass.Fill(jmsd, jpt, weight_mu)
                        self.h_msd_muCR4_N2_pass_mutriggerUp.Fill(jmsd, weight_mutriggerUp)
                        self.h_msd_muCR4_N2_pass_mutriggerDown.Fill(jmsd, weight_mutriggerDown)
                        self.h_msd_muCR4_N2_pass_muidUp.Fill(jmsd, weight_muidUp)
                        self.h_msd_muCR4_N2_pass_muidDown.Fill(jmsd, weight_muidDown)
                        self.h_msd_muCR4_N2_pass_muisoUp.Fill(jmsd, weight_muisoUp)
                        self.h_msd_muCR4_N2_pass_muisoDown.Fill(jmsd, weight_muisoDown)
                        self.h_msd_muCR4_N2_pass_PuUp.Fill(jmsd, weight_mu_pu_up)
                        self.h_msd_muCR4_N2_pass_PuDown.Fill(jmsd, weight_mu_pu_down)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_muCR4_N2_fail.Fill(jmsd, weight_mu)
                        self.h_msd_v_pt_muCR4_N2_fail.Fill(jmsd, jpt, weight_mu)
                        self.h_msd_muCR4_N2_fail_mutriggerUp.Fill(jmsd, weight_mutriggerUp)
                        self.h_msd_muCR4_N2_fail_mutriggerDown.Fill(jmsd, weight_mutriggerDown)
                        self.h_msd_muCR4_N2_fail_muidUp.Fill(jmsd, weight_muidUp)
                        self.h_msd_muCR4_N2_fail_muidDown.Fill(jmsd, weight_muidDown)
                        self.h_msd_muCR4_N2_fail_muisoUp.Fill(jmsd, weight_muisoUp)
                        self.h_msd_muCR4_N2_fail_muisoDown.Fill(jmsd, weight_muisoDown)
                        self.h_msd_muCR4_N2_fail_PuUp.Fill(jmsd, weight_mu_pu_up)
                        self.h_msd_muCR4_N2_fail_PuDown.Fill(jmsd, weight_mu_pu_down)
                    
                    if not self._minBranches:
                        dbcuts = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
                        for dbcut in dbcuts:
                            if jdb > dbcut:
                                getattr(self, 'h_msd_muCR4_N2_%s_pass' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_mutriggerUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mutriggerUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_mutriggerDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mutriggerDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_muidUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muidUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_muidDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muidDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_muisoUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muisoUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_muisoDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muisoDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_PuUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu_pu_up)
                                getattr(self, 'h_msd_muCR4_N2_%s_pass_PuDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu_pu_down)
                            elif jdb > self.DBTAGCUTMIN:
                                getattr(self, 'h_msd_muCR4_N2_%s_fail' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_mutriggerUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mutriggerUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_mutriggerDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mutriggerDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_muidUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muidUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_muidDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muidDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_muisoUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muisoUp)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_muisoDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_muisoDown)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_PuUp' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu_pu_up)
                                getattr(self, 'h_msd_muCR4_N2_%s_fail_PuDown' % str(dbcut).replace('0.','p')).Fill(jmsd, weight_mu_pu_down)

                            for syst in ['JESUp', 'JESDown', 'JERUp', 'JERDown']:
                              #print syst, dbcut, eval('jpt_%s' % syst), jmsd, isTightVJet, jdb
                              if eval('jpt_%s' % syst) > PTCUTMUCR and jmsd > MASSCUT and nmuLoose == 1 and neleLoose == 0 and ntau == 0 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and isTightVJet==1 and jtN2b1sdddt < 0 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3. and n_MdR0p8_4 >= 1:
                                if jdb > dbcut:
                                  (getattr(self, 'h_msd_muCR4_N2_%s_pass_%s' % (str(dbcut).replace('0.','p'),syst))).Fill(jmsd, weight)
                                  #print 'fill h_msd_muCR4_N2_%s_pass_%s'% (str(dbcut).replace('0.','p'),syst)
                                elif jdb > self.DBTAGCUTMIN:
                                  (getattr(self, 'h_msd_muCR4_N2_%s_fail_%s' % (str(dbcut).replace('0.','p'),syst))).Fill(jmsd, weight)
                                  #print 'fill h_msd_muCR4_N2_%s_fail_%s'% (str(dbcut).replace('0.','p'),syst)
            for syst in ['JESUp', 'JESDown', 'JERUp', 'JERDown']:
              if eval('jpt_%s' % syst) > PTCUTMUCR and jmsd > MASSCUT and nmuLoose == 1 and neleLoose == 0 and ntau == 0 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and isTightVJet==1 and jtN2b1sdddt < 0 and abs(math.acos(math.cos(vmuoLoose0_phi - jphi))) > 2. * ROOT.TMath.Pi() / 3. and n_MdR0p8_4 >= 1:
                if jdb > DBTAGCUT:
                  (getattr(self, 'h_msd_muCR4_N2_pass_%s' % syst)).Fill(jmsd, weight)
                elif jdb > self.DBTAGCUTMIN:
                  (getattr(self, 'h_msd_muCR4_N2_fail_%s' % syst)).Fill(jmsd, weight)

            if not self._minBranches:
                n_MPt100dR0p8_4_sub1 = self.nAK4PuppijetsMPt100dR08_1[0]
                n_MPt100dR0p8_4_sub2 = self.nAK4PuppijetsMPt100dR08_2[0]

                if not self._fillCA15:
                    jmsd_sub1 = self.AK8Puppijet1_msd[0]
                    jmsd_sub2 = self.AK8Puppijet2_msd[0]
                    jt21_sub1 = self.AK8Puppijet1_tau21[0]
                    jt21_sub2 = self.AK8Puppijet2_tau21[0]
                    isTightVJet_sub1 = self.AK8Puppijet1_isTightVJet
                    isTightVJet_sub2 = self.AK8Puppijet2_isTightVJet
                else:
                    jmsd_sub1 = self.CA15Puppijet1_msd[0]
                    jmsd_sub2 = self.CA15Puppijet2_msd[0]
                    jt21_sub1 = self.CA15Puppijet1_tau21[0]
                    jt21_sub2 = self.CA15Puppijet2_tau21[0]
                    isTightVJet_sub1 = self.CA15Puppijet1_isTightVJet
                    isTightVJet_sub2 = self.CA15Puppijet2_isTightVJet

                rhP_sub1 = -999
                jt21P_sub1 = -999
                if jpt_sub1 > 0 and jmsd_sub1 > 0:
                    rhP_sub1 = math.log(jmsd_sub1 * jmsd_sub1 / jpt_sub1)
                    jt21P_sub1 = jt21_sub1 + 0.063 * rhP_sub1

                rhP_sub2 = -999
                jt21P_sub2 = -999
                if jpt_sub2 > 0 and jmsd_sub2 > 0:
                    rhP_sub2 = math.log(jmsd_sub2 * jmsd_sub2 / jpt_sub2)
                    jt21P_sub2 = jt21_sub2 + 0.063 * rhP_sub2


                bb_idx = [[jmsd, jpt, jdb, n_MPt100dR0p8_4, jt21P, isTightVJet], [jmsd_sub1, jpt_sub1, jdb_sub1, n_MPt100dR0p8_4_sub1, jt21P_sub1, isTightVJet_sub1], [jmsd_sub2, jpt_sub2, jdb_sub2, n_MPt100dR0p8_4_sub2, jt21P_sub2, isTightVJet_sub2]]

                a = 0
                for i in sorted(bb_idx, key=lambda bbtag: bbtag[2], reverse=True):
                    if a > 0: continue
                    a = a + 1
                    if i[1] > PTCUTMUCR and i[0] > MASSCUT and nmuLoose == 1 and neleLoose == 0 and ntau == 0 and vmuoLoose0_pt > MUONPTCUT and abs(vmuoLoose0_eta) < 2.1 and i[4] < T21DDTCUT and i[5]:
                        if i[2] > DBTAGCUT:
                            self.h_msd_bbleading_muCR4_pass.Fill(i[0], weight_mu)
                            self.h_msd_v_pt_bbleading_muCR4_pass.Fill(i[0], i[1], weight_mu)
                        else:
                            self.h_msd_bbleading_muCR4_fail.Fill(i[0], weight_mu)
                            self.h_msd_v_pt_bbleading_muCR4_fail.Fill(i[0], i[1], weight_mu)
                if jpt > PTCUT:
                    cut[0] = cut[0] + 1
                if jpt > PTCUT and jmsd > MASSCUT:
                    cut[1] = cut[1] + 1
                if jpt > PTCUT and jmsd > MASSCUT and isTightVJet==1:
                    cut[2] = cut[2] + 1
                if jpt > PTCUT and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and nmuLoose == 0:
                    cut[3] = cut[3] + 1
                if jpt > PTCUT and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and nmuLoose == 0 and ntau == 0:
                    cut[4] = cut[4] + 1
                if jpt > PTCUT and jmsd > MASSCUT and isTightVJet==1 and neleLoose == 0 and nmuLoose == 0 and ntau == 0 and nphoLoose == 0:
                    cut[8] = cut[8] + 1

                if jpt > PTCUT:
                    self.h_msd_inc.Fill(jmsd, weight)
                    if jt21P < T21DDTCUT:
                        self.h_msd_t21ddtCut_inc.Fill(jmsd, weight)

            # Lepton and photon veto
            if neleLoose != 0 or nmuLoose != 0 or ntau != 0: continue  # or nphoLoose != 0:  continue

            if not self._minBranches:
                a = 0
                for i in sorted(bb_idx, key=lambda bbtag: bbtag[2], reverse=True):
                    if a > 0: continue
                    a = a + 1
                    if i[2] > DBTAGCUT and i[0] > MASSCUT and i[1] > PTCUT:
                        self.h_msd_bbleading.Fill(i[0], weight)
                        # print sorted(bb_idx, key=lambda bbtag: bbtag[2],reverse=True)
                        self.h_pt_bbleading.Fill(i[1], weight)
                        # print(i[0],i[1],i[2])
                        self.h_bb_bbleading.Fill(i[2], weight)
                    if i[1] > PTCUT and i[0] > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and i[3] < 2 and i[4] < T21DDTCUT and n_fwd_4 < 3 and i[5]:
                        if i[2] > DBTAGCUT:
                            self.h_msd_bbleading_topR6_pass.Fill(i[0], weight)
                            self.h_msd_v_pt_bbleading_topR6_pass.Fill(i[0], i[1], weight)
                        else:
                            self.h_msd_bbleading_topR6_fail.Fill(i[0], weight)
                            self.h_msd_v_pt_bbleading_topR6_fail.Fill(i[0], i[1], weight)

		if jpt > PTCUT and jmsd > MASSCUT:
	            self.h_rho_nocut.Fill(rh, weight)
                    self.h_n2b1sd_norhocut.Fill(jtN2b1sd, weight)
                    self.h_n2b1sdddt_norhocut.Fill(jtN2b1sdddt, weight)

                if jpt > PTCUT:
                    self.h_msd_nocut.Fill(jmsd, weight)
                    self.h_msd_raw_nocut.Fill(jmsd_raw, weight) 

                if jpt > PTCUT and jmsd > MASSCUT and rh < self._hrhocut and rh > self._lrhocut:
                    self.h_pt.Fill(jpt, weight)
                    self.h_eta.Fill(jeta, weight)
                    self.h_pt_sub1.Fill(jpt_sub1, weight)
                    self.h_pt_sub2.Fill(jpt_sub2, weight)
                    self.h_msd.Fill(jmsd, weight)
		    self.h_rho.Fill(rh, weight)
                    self.h_msd_raw.Fill(jmsd_raw, weight)
                    self.h_dbtag.Fill(jdb, weight)
                    self.h_dbtag_sub1.Fill(jdb_sub1, weight)
                    self.h_dbtag_sub2.Fill(jdb_sub2, weight)
                    self.h_t21.Fill(jt21, weight)
                    self.h_t32.Fill(jt32, weight)
                    self.h_t21ddt.Fill(jt21P, weight)
                    self.h_rhop_v_t21.Fill(rhP, jt21, weight)
                    self.h_n2b1sd.Fill(jtN2b1sd, weight)
                    self.h_n2b1sdddt.Fill(jtN2b1sdddt, weight)
		
                    self.h_n_ak4.Fill(n_4, weight)
                    self.h_n_ak4_dR0p8.Fill(n_dR0p8_4, weight)
                    self.h_n_ak4fwd.Fill(n_fwd_4, weight)
                    self.h_n_ak4L.Fill(n_LdR0p8_4, weight)
                    self.h_n_ak4L100.Fill(n_LPt100dR0p8_4, weight)
                    self.h_n_ak4M.Fill(n_MdR0p8_4, weight)
                    self.h_n_ak4M100.Fill(n_MPt100dR0p8_4, weight)
                    self.h_n_ak4T.Fill(n_TdR0p8_4, weight)
                    self.h_n_ak4T100.Fill(n_TPt100dR0p8_4, weight)
                    self.h_n_ak4L150.Fill(n_LPt150dR0p8_4, weight)
                    self.h_n_ak4M150.Fill(n_MPt150dR0p8_4, weight)
                    self.h_n_ak4T150.Fill(n_TPt150dR0p8_4, weight)
                    self.h_isolationCA15.Fill(ratioCA15_04, weight)
                    self.h_met.Fill(met, weight)

                if jpt > PTCUT and jt21P < T21DDTCUT and jmsd > MASSCUT:
                    self.h_msd_t21ddtCut.Fill(jmsd, weight)
                    self.h_t32_t21ddtCut.Fill(jt32, weight)

                if jpt > PTCUT and jtN2b1sdddt < 0 and jmsd > MASSCUT:
                    self.h_msd_N2Cut.Fill(jmsd, weight)

                if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and n_TdR0p8_4 < 3 and isTightVJet==1:
                    self.h_msd_topR1.Fill(jmsd, weight)
                    self.h_msd_v_pt_topR1.Fill(jmsd, jpt, weight)
                if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and n_TdR0p8_4 < 3 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        self.h_msd_topR2_pass.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR2_pass.Fill(jmsd, jpt, weight)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_topR2_fail.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR2_fail.Fill(jmsd, jpt, weight)
                if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and n_TdR0p8_4 < 3 and jt21P < 0.4 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        self.h_msd_topR3_pass.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR3_pass.Fill(jmsd, jpt, weight)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_topR3_fail.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR3_fail.Fill(jmsd, jpt, weight)
                if jpt > PTCUT and jmsd > MASSCUT and jt21P < 0.4 and jt32 > 0.7 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        self.h_msd_topR4_pass.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR4_pass.Fill(jmsd, jpt, weight)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_topR4_fail.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR4_fail.Fill(jmsd, jpt, weight)
                if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and n_MPt100dR0p8_4 < 2 and jt21P < T21DDTCUT and n_fwd_4 < 3 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        self.h_msd_topR5_pass.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR5_pass.Fill(jmsd, jpt, weight)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_topR5_fail.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR5_fail.Fill(jmsd, jpt, weight)

            if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and isTightVJet==1:
                cut[5] = cut[5] + 1
            #if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and isTightVJet==1:
                #cut[7] = cut[7] + 1
            if (not self._minBranches) and jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and jt21P < T21DDTCUT and isTightVJet==1:
                if jdb > DBTAGCUT:
                    # cut[9]=cut[9]+1
                    self.h_msd_topR6_pass.Fill(jmsd, weight)
                    self.h_msd_raw_SR_pass.Fill(jmsd_raw, weight)
                    self.h_msd_v_pt_topR6_pass.Fill(jmsd, jpt, weight)
                    self.h_msd_v_pt_topR6_raw_pass.Fill(jmsd_raw, jpt, weight)
                    # for signal morphing
                    if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                        self.h_msd_v_pt_topR6_pass_matched.Fill(jmsd, jpt, weight)
                    else:
                        self.h_msd_v_pt_topR6_pass_unmatched.Fill(jmsd, jpt, weight)
                elif jdb > self.DBTAGCUTMIN:
                    self.h_msd_topR6_fail.Fill(jmsd, weight)
                    self.h_msd_v_pt_topR6_fail.Fill(jmsd, jpt, weight)
                    self.h_msd_raw_SR_fail.Fill(jmsd_raw, weight)
                    self.h_msd_v_pt_topR6_raw_fail.Fill(jmsd, jpt, weight)
                    # for signal morphing
                    if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                        self.h_msd_v_pt_topR6_fail_matched.Fill(jmsd, jpt, weight)
                    else:
                        self.h_msd_v_pt_topR6_fail_unmatched.Fill(jmsd, jpt, weight)
	    if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and isTightVJet==1 and jdb > DBTAGCUT and rh < self._hrhocut and rh > self._lrhocut: 	
		if (not self._minBranches): self.h_n2b1sdddt_aftercut.Fill(jtN2b1sdddt,weight)
            if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and jtN2b1sdddt < 0 and isTightVJet==1:
                cut[6] = cut[6] + 1
		if  rh < self._hrhocut and rh > self._lrhocut:
		    cut[7] = cut[7] + 1
		    if (not self._minBranches): self.h_dbtag_aftercut.Fill(jdb,weight)
                if jdb > DBTAGCUT:
                    cut[9] = cut[9] + 1
                    self.h_msd_topR6_N2_pass.Fill(jmsd, weight)
                    self.h_msd_v_pt_topR6_N2_pass.Fill(jmsd, jpt, weight)
                    self.h_msd_v_pt_topR6_N2_pass_triggerUp.Fill(jmsd, jpt, weight_triggerUp)
                    self.h_msd_v_pt_topR6_N2_pass_triggerDown.Fill(jmsd, jpt, weight_triggerDown)
                    self.h_msd_v_pt_topR6_N2_pass_PuUp.Fill(jmsd, jpt, weight_pu_up)
                    self.h_msd_v_pt_topR6_N2_pass_PuDown.Fill(jmsd, jpt, weight_pu_down)

                    # for signal morphing
                    if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                        self.h_msd_v_pt_topR6_N2_pass_matched.Fill(jmsd, jpt, weight)
                    else:
                        self.h_msd_v_pt_topR6_N2_pass_unmatched.Fill(jmsd, jpt, weight)
                elif jdb > self.DBTAGCUTMIN:
                    self.h_msd_topR6_N2_fail.Fill(jmsd, weight)
                    self.h_msd_v_pt_topR6_N2_fail.Fill(jmsd, jpt, weight)
                    self.h_msd_v_pt_topR6_N2_fail_triggerUp.Fill(jmsd, jpt, weight_triggerUp)
                    self.h_msd_v_pt_topR6_N2_fail_triggerDown.Fill(jmsd, jpt, weight_triggerDown)
                    self.h_msd_v_pt_topR6_N2_fail_PuUp.Fill(jmsd, jpt, weight_pu_up)
                    self.h_msd_v_pt_topR6_N2_fail_PuDown.Fill(jmsd, jpt, weight_pu_down)

                    # for signal morphing
                    if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                        self.h_msd_v_pt_topR6_N2_fail_matched.Fill(jmsd, jpt, weight)
                    else:
                        self.h_msd_v_pt_topR6_N2_fail_unmatched.Fill(jmsd, jpt, weight)

            for syst in ['JESUp', 'JESDown', 'JERUp', 'JERDown']:
                if (not self._minBranches) and eval('jpt_%s' % syst) > PTCUT and jmsd > MASSCUT and eval('met_%s' % syst) < METCUT and eval('n_dR0p8_4_%s' % syst) < NJETCUT and jt21P < T21DDTCUT and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        (getattr(self, 'h_msd_topR6_pass_%s' % syst)).Fill(jmsd, weight)
                        (getattr(self, 'h_msd_v_pt_topR6_pass_%s' % syst)).Fill(jmsd, eval('jpt_%s' % syst), weight)
                    elif jdb > self.DBTAGCUTMIN:
                        (getattr(self, 'h_msd_topR6_fail_%s' % syst)).Fill(jmsd, weight)
                        (getattr(self, 'h_msd_v_pt_topR6_fail_%s' % syst)).Fill(jmsd, eval('jpt_%s' % syst), weight)
                if eval('jpt_%s' % syst) > PTCUT and jmsd > MASSCUT and eval('met_%s' % syst) < METCUT and eval( 'n_dR0p8_4_%s' % syst) < NJETCUT and jtN2b1sdddt < 0 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        (getattr(self, 'h_msd_topR6_N2_pass_%s' % syst)).Fill(jmsd, weight)
                        (getattr(self, 'h_msd_v_pt_topR6_N2_pass_%s' % syst)).Fill(jmsd, eval('jpt_%s' % syst), weight)
                    elif jdb > self.DBTAGCUTMIN:
                        (getattr(self, 'h_msd_topR6_N2_fail_%s' % syst)).Fill(jmsd, weight)
                        (getattr(self, 'h_msd_v_pt_topR6_N2_fail_%s' % syst)).Fill(jmsd, eval('jpt_%s' % syst), weight)
            ###Double-b optimization for ggH
            if not self._minBranches:
                dbcuts = [0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
                for dbcut in dbcuts:
                    # using tau21DDT
                    if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and jt21P < T21DDTCUT and isTightVJet==1:
                        if jdb > dbcut:
                            getattr(self,'h_msd_topR6_%s_pass'%str(dbcut).replace('0.','p')).Fill(jmsd, weight)
                            getattr(self,'h_msd_v_pt_topR6_%s_pass'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            getattr(self,'h_msd_v_pt_topR6_%s_pass_PuUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_up)
                            getattr(self,'h_msd_v_pt_topR6_%s_pass_PuDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_down)
                            getattr(self,'h_msd_v_pt_topR6_%s_pass_triggerUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerUp)
                            getattr(self,'h_msd_v_pt_topR6_%s_pass_triggerDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerDown)
                            # for signal morphing
                            if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                                getattr(self,'h_msd_v_pt_topR6_%s_pass_matched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            else: 
                                getattr(self,'h_msd_v_pt_topR6_%s_pass_unmatched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                        else:
                            getattr(self,'h_msd_topR6_%s_fail'%str(dbcut).replace('0.','p')).Fill(jmsd, weight)
                            getattr(self,'h_msd_v_pt_topR6_%s_fail'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            getattr(self,'h_msd_v_pt_topR6_%s_fail_PuUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_up)
                            getattr(self,'h_msd_v_pt_topR6_%s_fail_PuDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_down)
                            getattr(self,'h_msd_v_pt_topR6_%s_fail_triggerUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerUp)
                            getattr(self,'h_msd_v_pt_topR6_%s_fail_triggerDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerDown)
                            # for signal morphing
                            if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                                getattr(self,'h_msd_v_pt_topR6_%s_fail_matched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            else: 
                                getattr(self,'h_msd_v_pt_topR6_%s_fail_unmatched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                    for syst in ['JESUp', 'JESDown', 'JERUp', 'JERDown']:
                      if eval('jpt_%s' % syst) > PTCUT and jmsd > MASSCUT and eval('met_%s' % syst) < METCUT and eval('n_dR0p8_4_%s' % syst) < NJETCUT and jt21P < T21DDTCUT and isTightVJet==1:
                        getattr(self, 'h_msd_v_pt_topR6_%s_pass_%s' % (str(dbcut).replace('0.','p'),syst)).Fill(jmsd, eval('jpt_%s' % syst),weight)
                      else:
                        getattr(self, 'h_msd_v_pt_topR6_%s_fail_%s' % (str(dbcut).replace('0.','p'),syst)).Fill(jmsd, eval('jpt_%s' % syst),weight)
                    # using N2DDT
                    if jpt > PTCUT and jmsd > MASSCUT and met < METCUT and n_dR0p8_4 < NJETCUT and jtN2b1sdddt < 0 and isTightVJet==1:
                        if jdb > dbcut:
                            getattr(self,'h_msd_topR6_N2_%s_pass'%str(dbcut).replace('0.','p')).Fill(jmsd, weight)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_pass'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_PuUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_up)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_PuDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_down)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_triggerUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerUp)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_triggerDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerDown)
                            # for signal morphing
                            if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                                getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_matched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            else: 
                                getattr(self,'h_msd_v_pt_topR6_N2_%s_pass_unmatched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                        else:
                            getattr(self,'h_msd_topR6_N2_%s_fail'%str(dbcut).replace('0.','p')).Fill(jmsd, weight)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_fail'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_PuUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_up)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_PuDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_pu_down)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_triggerUp'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerUp)
                            getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_triggerDown'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight_triggerDown)
                            # for signal morphing
                            if dphi < 0.8 and dpt < 0.5 and dmass < 0.3:
                                getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_matched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                            else: 
                                getattr(self,'h_msd_v_pt_topR6_N2_%s_fail_unmatched'%str(dbcut).replace('0.','p')).Fill(jmsd, jpt, weight)
                    for syst in ['JESUp', 'JESDown', 'JERUp', 'JERDown']:
                      #print dbcut, syst, eval('jpt_%s' % syst), eval('met_%s' % syst), eval('n_dR0p8_4_%s' % syst), jtN2b1sdddt, isTightVJet==1, jdb
                      if eval('jpt_%s' % syst) > PTCUT and jmsd > MASSCUT and eval('met_%s' % syst) < METCUT and eval('n_dR0p8_4_%s' % syst) < NJETCUT and jtN2b1sdddt < 0 and isTightVJet==1:
                        if jdb > dbcut:
                          getattr(self, 'h_msd_v_pt_topR6_N2_%s_pass_%s' % (str(dbcut).replace('0.','p'),syst)).Fill(jmsd, eval('jpt_%s' % syst),weight)
                          #print 'fill h_msd_v_pt_topR6_N2_%s_pass_%s' % (str(dbcut).replace('0.','p'),syst)
                        else:
                          getattr(self, 'h_msd_v_pt_topR6_N2_%s_fail_%s' % (str(dbcut).replace('0.','p'),syst)).Fill(jmsd, eval('jpt_%s' % syst),weight)
                          #print 'fill h_msd_v_pt_topR6_N2_%s_fail_%s' % (str(dbcut).replace('0.','p'),syst)

                ################################
                if jpt > PTCUT and jmsd > MASSCUT and jpt_sub1 < 300 and met < METCUT and n_dR0p8_4 < NJETCUT and n_TdR0p8_4 < 3 and jt21P < 0.4 and isTightVJet==1:
                    if jdb > DBTAGCUT:
                        self.h_msd_topR7_pass.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR7_pass.Fill(jmsd, jpt, weight)
                    elif jdb > self.DBTAGCUTMIN:
                        self.h_msd_topR7_fail.Fill(jmsd, weight)
                        self.h_msd_v_pt_topR7_fail.Fill(jmsd, jpt, weight)

                if jpt > PTCUT and jdb > DBTAGCUT and jmsd > MASSCUT:
                    self.h_msd_dbtagCut.Fill(jmsd, weight)
                    self.h_pt_dbtagCut.Fill(jpt, weight)

        print "\n"
       # Signal 
        if not self._minBranches and cut[0] > 0.:
            self.h_Cuts.SetBinContent(1, float(cut[0]))# / den * 100.))
            self.h_Cuts.SetBinContent(2, float(cut[1]))# / den * 100.))
            self.h_Cuts.SetBinContent(3, float(cut[2]))# / den * 100.))
            self.h_Cuts.SetBinContent(4, float(cut[3]))# / den * 100.))
            self.h_Cuts.SetBinContent(5, float(cut[4]))# / den * 100.))
            self.h_Cuts.SetBinContent(6, float(cut[5]))# / den * 100.))
            self.h_Cuts.SetBinContent(7, float(cut[6]))# / den * 100.))
            self.h_Cuts.SetBinContent(8, float(cut[7]))# / den * 100.))
            a_Cuts = self.h_Cuts.GetXaxis()
            a_Cuts.SetBinLabel(1, "p_{{T}}>{} GeV".format(PTCUT))
            a_Cuts.SetBinLabel(2, "m_{{SD}}>{} GeV".format(MASSCUT))
            a_Cuts.SetBinLabel(3, "tight ID")
            a_Cuts.SetBinLabel(4, "lep veto")
            a_Cuts.SetBinLabel(5, "#tau veto")
            a_Cuts.SetBinLabel(6, "MET<" + str(METCUT))
            a_Cuts.SetBinLabel(7, "N_{2}^{DDT}<0")
	    a_Cuts.SetBinLabel(8, "{}<#rho<{}".format(self._lrhocut, self._hrhocut))
            print "p_{{T}}>{} GeV".format(PTCUT) , int(cut[0]), " \n"
            print "m_{{SD}}>{} GeV".format(MASSCUT), int(cut[1]), " \n" 
            print "tight ID", int(cut[2]), " \n"
            print "lep veto", int(cut[3]), " \n" 
            print "tau veto", int(cut[4]), " \n"
            print "MET<" + str(METCUT), int(cut[5]), " \n" 
            print "N2^{DDT}<0", int(cut[6]), " \n"
            print "{}<#rho<{}".format(self._lrhocut, self._hrhocut), int(cut[7]), " \n" 
            print(cut[3] / nent * 100., cut[7], cut[6], cut[9])

            self.h_Cuts_p.SetBinContent(1, float(cut[0]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(2, float(cut[1]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(3, float(cut[2]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(4, float(cut[3]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(5, float(cut[4]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(6, float(cut[5]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(7, float(cut[6]/cut[0])  * 100.)
            self.h_Cuts_p.SetBinContent(8, float(cut[7]/cut[0])  * 100.)
            a_Cuts_p = self.h_Cuts_p.GetXaxis()
            a_Cuts_p.SetBinLabel(1, "p_{{T}}>{} GeV".format(PTCUT))
            a_Cuts_p.SetBinLabel(2, "m_{{SD}}>{} GeV".format(MASSCUT))
            a_Cuts_p.SetBinLabel(3, "tight ID")
            a_Cuts_p.SetBinLabel(4, "lep veto")
            a_Cuts_p.SetBinLabel(5, "#tau veto")
            a_Cuts_p.SetBinLabel(6, "MET<" + str(METCUT))
            a_Cuts_p.SetBinLabel(7, "N_{2}^{DDT}<0")
	    a_Cuts_p.SetBinLabel(8, "{}<#rho<{}".format(self._lrhocut, self._hrhocut))
            #a_Cuts.SetBinLabel(9, "Double b-tag > " + str(DBTAGCUT))

       # Muon 
        if not self._minBranches and cut[0] > 0.:
            self.h_Cuts_muon.SetBinContent(1, float(cut_muon[0]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(2, float(cut_muon[1]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(3, float(cut_muon[2]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(4, float(cut_muon[3]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(5, float(cut_muon[4]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(6, float(cut_muon[5]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(7, float(cut_muon[6]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(8, float(cut_muon[7]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(9, float(cut_muon[8]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(10, float(cut_muon[9]))# / den * 100.))
            self.h_Cuts_muon.SetBinContent(11, float(cut_muon[10]))# / den * 100.))
            a_Cuts_muon = self.h_Cuts_muon.GetXaxis()
            a_Cuts_muon.SetBinLabel(1, "p_{{T}}>{} GeV".format(PTCUTMUCR))
            a_Cuts_muon.SetBinLabel(2, "m_{{SD}}>{} GeV".format(MASSCUT))
            a_Cuts_muon.SetBinLabel(3, "tight ID")
            a_Cuts_muon.SetBinLabel(4, "e veto")
            a_Cuts_muon.SetBinLabel(5, "#tau veto")
            a_Cuts_muon.SetBinLabel(6, "#mu veto")
            a_Cuts_muon.SetBinLabel(7, "p_{{T}}(#mu)>{} GeV".format(MUONPTCUT))
            a_Cuts_muon.SetBinLabel(8, "|#eta(#mu)| < 2.1")
            a_Cuts_muon.SetBinLabel(9, "#Delta#phi(#mu,j) < #frac{2#pi}{3}")
            a_Cuts_muon.SetBinLabel(10, "n_MdR0p8_4 >=1")
            a_Cuts_muon.SetBinLabel(11, "N_{2}^{DDT}<0")

            self.h_Cuts_muon_p.SetBinContent(1, float(cut_muon[0]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(2, float(cut_muon[1]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(3, float(cut_muon[2]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(4, float(cut_muon[3]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(5, float(cut_muon[4]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(6, float(cut_muon[5]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(7, float(cut_muon[6]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(8, float(cut_muon[7]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(9, float(cut_muon[8]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(10, float(cut_muon[9]/cut_muon[0])  * 100.)
            self.h_Cuts_muon_p.SetBinContent(11, float(cut_muon[10]/cut_muon[0])  * 100.)
            a_Cuts_muon_p = self.h_Cuts_muon_p.GetXaxis()
            a_Cuts_muon_p.SetBinLabel(1, "p_{{T}}>{} GeV".format(PTCUTMUCR))
            a_Cuts_muon_p.SetBinLabel(2, "m_{{SD}}>{} GeV".format(MASSCUT))
            a_Cuts_muon_p.SetBinLabel(3, "tight ID")
            a_Cuts_muon_p.SetBinLabel(4, "e veto")
            a_Cuts_muon_p.SetBinLabel(5, "#tau veto")
            a_Cuts_muon_p.SetBinLabel(6, "#mu veto")
            a_Cuts_muon_p.SetBinLabel(7, "p_{{T}}(#mu)>{} GeV".format(MUONPTCUT))
            a_Cuts_muon_p.SetBinLabel(8, "|#eta(#mu)| < 2.1")
            a_Cuts_muon_p.SetBinLabel(9, "#Delta#phi(#mu,j) < #frac{2#pi}{3}")
            a_Cuts_muon_p.SetBinLabel(10, "n_MdR0p8_4 >=1")
            a_Cuts_muon_p.SetBinLabel(11, "N_{2}^{DDT}<0")

            self.h_rhop_v_t21_Px = self.h_rhop_v_t21.ProfileX()
            self.h_rhop_v_t21_Px.SetTitle("; rho^{DDT}; <#tau_{21}>")

    def PUPPIweight(self, puppipt=30., puppieta=0.):

        genCorr = 1.
        recoCorr = 1.
        totalWeight = 1.

        genCorr = self.corrGEN.Eval(puppipt)
        if (abs(puppieta) < 1.3):
            recoCorr = self.corrRECO_cen.Eval(puppipt)
        else:
            recoCorr = self.corrRECO_for.Eval(puppipt)
        totalWeight = genCorr * recoCorr
        return totalWeight

##########################################################################################
